# Validate raw → staging — Commit real: 24 propiedades

- Fecha: 2026-06-06 (continuación sesión 2026-06-06)
- Modo: **commit** (accion_final=commit — filas reales insertadas en Neon)
- Filtro: `--source captured_json --created-after 2026-06-06T00:00:00 --limit 30`
- Origen: `propiedades_raw` (batch `internal_batch_20260606_1129`)
- Destino: `propiedades_staging`
- Fixes activos al momento del commit: A + B + C + D + E + G

---

## Resultado ejecutivo

| Métrica | Valor |
|---|---|
| filas_leidas | **24** |
| validadas | **24** |
| rechazadas | **0** |
| duplicadas | **0** |
| accion_final | **commit** |
| staging insertadas (verificado en Neon) | **24** |

---

## Issues registrados (solo soft — ninguno bloqueó staging)

| Issue | Count | Significado |
|---|---|---|
| `geocoding_skipped_approx_location` | 14 | Sin dirección precisa, solo ciudad/provincia — skip correcto |
| `location_inferred_from_text` | 21 | Fix A: ciudad/provincia inferidos desde hostname ✅ |
| `missing_location` | 3 | Watson: sin token de hostname coincidente — correcto |

---

## Staging verification — datos reales en Neon

### innoacafayate.com — 17 props (id: 5282)

| Campo | Resultado en staging |
|---|---|
| ciudad | **17 × Cafayate** ← Fix A ✅ |
| provincia | **17 × Salta** ← Fix A ✅ |
| direccion_normalizada | 7 con dirección real · 10 NULL (Fix C) |
| precio | 9 con precio · 8 NULL |
| geocoding_status | **7 × pending** (geocodificables) · **10 × skipped** (sin dir. precisa) |
| avg validation_score | **87.6** |

Scores individuales confirmados:
- Con dirección + precio: **score=100** (Fix A +15 sobre el 85 estimado antes de Fix A)
- Sin dirección + precio: **score=95** (-5 por geocoding_skipped)

### camposdelapampa.com.ar — 4 props (id: 1443)

| Campo | Resultado en staging |
|---|---|
| ciudad | NULL (hostname solo da provincia, no ciudad específica) |
| provincia | **4 × La Pampa** ← Fix A ✅ |
| tipo_propiedad | **4 × campo** ← Fix E ✅ |
| direccion_normalizada | NULL (Fix D) |
| precio | NULL |
| geocoding_status | **4 × skipped** (tienen provincia, sin dirección precisa) |
| avg validation_score | **75.0** |

### watsonpropiedades.com — 3 props (id: 6162)

| Campo | Resultado en staging |
|---|---|
| ciudad | NULL |
| provincia | NULL |
| direccion_normalizada | NULL |
| precio | NULL (Fix F pendiente) |
| geocoding_status | **3 × pending** |
| avg validation_score | **65.0** |

---

## Estado post-commit en Neon (verificado)

| Tabla | Cambio |
|---|---|
| `propiedades_raw` | 24 filas → `status=validated` ✅ |
| `propiedades_staging` | +24 filas `status=staging` · `staged_at=CURRENT_DATE` ✅ |
| `geocoding_results` | Sin cambios (0 nuevas hoy) ✅ |
| `scraping_run_items` | Sin cambios ✅ |

---

## Comparativa con dry-run (antes → después del commit)

| Métrica | Dry-run (post Fix A) | Commit real | Match |
|---|---|---|---|
| filas_leidas | 24 | 24 | ✅ |
| validadas | 24 | 24 | ✅ |
| rechazadas | 0 | 0 | ✅ |
| duplicadas | 0 | 0 | ✅ |
| location_inferred_from_text | 21 | 21 | ✅ |
| missing_location | 3 | 3 | ✅ |
| geocoding_skipped_approx_location | 14 | 14 | ✅ |
| avg_score innoacafayate | ~87–100 (estimado) | 87.6 (real) | ✅ |
| avg_score camposdelapampa | ~75 (estimado) | 75.0 (real) | ✅ |
| avg_score watson | ~65 (estimado) | 65.0 (real) | ✅ |

Dry-run → commit: 100% consistente. Sin sorpresas.

---

## Confirmación de seguridad

| Verificación | Estado |
|---|---|
| Supabase tocado | ✗ NO |
| publish_to_supabase.py ejecutado | ✗ NO |
| publish_queue modificado | ✗ NO |
| geocoding ejecutado | ✗ NO |
| geocoding_results nuevas hoy | 0 (verificado en Neon) |
| frontend modificado | ✗ NO |
| `.env` modificado | ✗ NO |
| git commit | ✗ NO |
| git push | ✗ NO |
| datos borrados | ✗ NO |
| schema modificado | ✗ NO |

---

## Resumen de fixes aplicados a estas 24 propiedades

| Fix | Issue resuelto | Props afectadas |
|---|---|---|
| **A** — location desde hostname | missing_location: 24 → 3 | 21/24 |
| **B** — operación desde URL path | operacion incorrecta (alquiler marcado como venta) | 6/17 innoacafayate |
| **C** — office address nullificado | "San Martin 191" como dirección de oficina | 10/17 innoacafayate |
| **D** — dominio como dirección | "camposdelapampa.com.ar" como dirección | 4/4 camposdelapampa |
| **E** — tipo desde dominio rural | `departamento` → `campo` | 3/4 camposdelapampa |
| **G** — *(aplicado en import)* | test_mode_id desde batch CSV | 24/24 |

---

## Próximo paso recomendado: geocoding dry-run

Ver sección siguiente (FASE 5) para el comando preparado.

**7 propiedades de innoacafayate** tienen `ciudad=Cafayate, provincia=Salta` + dirección real:
→ Candidatas a geocoding de alta precisión.

**14 propiedades** tienen `geocoding_status=skipped` → El geocoder las saltará correctamente.

**3 propiedades de watson** tienen `geocoding_status=pending` sin datos útiles → El geocoder las marcará como skipped o fallará sin consumir créditos de API (depende de implementación).

---

*Generado automáticamente al finalizar validate_raw_properties.py --commit · sesión 2026-06-06*
