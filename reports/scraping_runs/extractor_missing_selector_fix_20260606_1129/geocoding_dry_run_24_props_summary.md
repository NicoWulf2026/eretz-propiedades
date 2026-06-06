# Geocoding dry-run — 24 props batch (10 pending)

- Fecha: 2026-06-06
- Modo: **dry-run** (rollback — sin llamadas a Nominatim, sin escritura en Neon)
- Proveedor: Nominatim (OSM)
- Filtro: `--ids-file geocoding_ids_24_props.csv` (10 staging_ids exactos)
- Origen: propiedades_staging del batch `internal_batch_20260606_1129`

---

## ALERTA DE SEGURIDAD — por qué obligatorio usar --ids-file

| Filtro | Pending que procesaría | Veredicto |
|---|---|---|
| `--source captured_json` (sin fecha) | **42.146 filas** (2026-06-01 a 2026-06-05) | ⛔ PELIGROSO |
| `--ids-file` con 10 staging_ids exactos | **10 filas** (solo el batch de hoy) | ✅ SEGURO |

**Conclusión: siempre usar `--ids-file` para este batch.**

---

## Resultado del dry-run

| Métrica | Valor |
|---|---|
| filas_leidas | **10** |
| probe (intentaría geocodificar) | **7** |
| skipped (descartadas inmediatamente) | **3** |
| done | 0 (dry-run) |
| failed | 0 (dry-run) |
| requests_usados | **0** (rollback confirmado) |
| accion_final | rollback |

---

## Desglose de las 10 filas

### Grupo A — 7 PROBE (innoacafayate — geocodificables)

| staging_id | tipo | operación | score | direccion_normalizada | string enviado a Nominatim |
|---|---|---|---|---|---|
| 81036 | terreno | venta | 100 | Haras La Querencia 800 | `Haras La Querencia 800, Cafayate, Salta, Argentina` |
| 81038 | casa | venta | 100 | Casa Pueblo Nuevo Mza. 21 | `Casa Pueblo Nuevo Mza. 21, Cafayate, Salta, Argentina` |
| 81041 | terreno | venta | 80 | Pueblo Nuevo Mza. 69 | `Pueblo Nuevo Mza. 69, Cafayate, Salta, Argentina` |
| 81042 | terreno | venta | 80 | Pueblo Nuevo Mza. 46 | `Pueblo Nuevo Mza. 46, Cafayate, Salta, Argentina` |
| 81044 | terreno | venta | 80 | Pueblo Nuevo Mza. 127 | `Pueblo Nuevo Mza. 127, Cafayate, Salta, Argentina` |
| 81047 | local | alquiler | 100 | Local calle Salta 329 | `Local calle Salta 329, Cafayate, Salta, Argentina` |
| 81048 | casa | alquiler | 80 | Casa Vertientes 57 | `Casa Vertientes 57, Cafayate, Salta, Argentina` |

### Grupo B — 3 SKIPPED inmediatamente (watson — sin datos útiles)

| staging_id | motivo | ciudad | provincia | direccion |
|---|---|---|---|---|
| 81057 | garbage_address | NULL | NULL | NULL |
| 81058 | garbage_address | NULL | NULL | NULL |
| 81059 | garbage_address | NULL | NULL | NULL |

Nominatim **NO sería llamado** para los 3 watson. El geocoder los detecta como `garbage_address` antes de llamar a la API.

---

## Análisis de precisión esperada (commit real)

| staging_id | Dirección | Precisión estimada | Motivo |
|---|---|---|---|
| 81047 | calle Salta 329 | **ALTA** | Calle + número en ciudad pequeña — formato estándar en OSM |
| 81048 | Casa Vertientes 57 | **MEDIA** | "Vertientes" puede ser calle o barrio en Cafayate; 57 como número |
| 81036 | Haras La Querencia 800 | **BAJA-MEDIA** | Nombre de propiedad privada; "800" probablemente Ha, no numeración vial |
| 81038 | Pueblo Nuevo Mza. 21 | **BAJA** | "Mza." = Manzana (loteo) — referencia catastral, no calle OSM |
| 81041 | Pueblo Nuevo Mza. 69 | **BAJA** | Igual que anterior |
| 81042 | Pueblo Nuevo Mza. 46 | **BAJA** | Igual que anterior |
| 81044 | Pueblo Nuevo Mza. 127 | **BAJA** | Igual que anterior |

**Resultado esperado en commit:**
- 1–2 props: `geocoding_status=done` con alta precisión (calle Salta 329, posiblemente Vertientes 57)
- 2–4 props: `geocoding_status=done` con precisión baja/barrio (Nominatim puede devolver Pueblo Nuevo como barrio)
- 1–2 props: `geocoding_status=failed` (Nominatim no encuentra referencia catastral)
- 3 props watson: `geocoding_status=skipped` (sin datos — 0 llamadas a Nominatim)

---

## Cantidad real de requests a Nominatim en commit

| Caso | Calls a Nominatim |
|---|---|
| Máximo posible (7 probe todas intentadas) | **7** |
| Mínimo posible (fallas rápidas sin hit) | 7 (Nominatim se llama igual, devuelve 0 resultados) |
| Watson (garbage_address) | **0** (skip antes de la llamada) |
| **Total estimado** | **7 calls** |

Con `--max-requests 10` hay margen suficiente. No se alcanzaría el tope.

---

## Verificación de seguridad pre-dry-run

| Verificación | Resultado |
|---|---|
| Procesos Python activos | **0** ✅ |
| geocoding_results existentes para estos 7 staging_ids | **0** (ningún resultado previo) ✅ |
| --source sin ids-file tomaría histórico | **42.146 filas** — por eso se usa ids-file ⚠️ |
| ids_file cargados correctamente | **10 IDs** ✅ |
| requests_usados en dry-run | **0** ✅ |
| accion_final | **rollback** ✅ |

---

## Estado del batch completo (24 props) tras este dry-run

| Grupo | Props | geocoding_status actual | Cambiaría en commit |
|---|---|---|---|
| innoacafayate con dirección | 7 | pending | → done / failed según Nominatim |
| innoacafayate sin dirección | 10 | skipped | Sin cambio (no son pending) |
| camposdelapampa | 4 | skipped | Sin cambio (no son pending) |
| watson | 3 | pending | → skipped (garbage_address, 0 calls) |

---

## Riesgos

| Riesgo | Severidad | Mitigación |
|---|---|---|
| Nominatim no conoce "Mza. 21/46/69/127" | BAJA | Resultado: failed — no borra datos, solo marca geocoding_status=failed |
| Nominatim devuelve coordenadas del centro de Cafayate | BAJA | Precisión baja pero coords válidas — aceptable para ubicar en mapa |
| "Haras La Querencia 800" geocodificado como ruta | BAJA | Si falla → failed; si acierta → coords aproximadas del haras |
| Rate limit Nominatim (max 1 req/s) | BAJA | 7 requests con delay 1s = ~10 segundos total — dentro del límite |
| --source sin ids-file | ALTA | Mitigado: usando ids-file con 10 IDs exactos |

---

## ¿Conviene hacer commit?

**Sí — con consideraciones:**

1. **Las 7 calls a Nominatim son legítimas** — direcciones reales de Cafayate con ciudad+provincia confirmados.
2. **Resultados parciales son normales** — Nominatim puede fallar en referencias catastrales (Mza. X) sin romper el pipeline. Los fallidos quedan en `geocoding_status=failed` y pueden re-intentarse.
3. **Los 3 watson se resolverán en 0 calls** — pasarán de `pending` a `skipped`, limpiando la cola.
4. **Sin riesgo de datos históricos** — el ids-file garantiza aislamiento.

**Resultado esperado realista en commit:**
- 1–3 props `done` con coordenadas válidas (calle Salta 329 segura, Vertientes 57 probable)
- 2–4 props `done` con precisión baja (barrio Pueblo Nuevo)
- 0–2 props `failed` (referencias catastrales que Nominatim no conoce)
- 3 props `skipped` (watson — sin datos)

---

## Comando para commit (NO ejecutar sin autorización)

```bash
USE_INTERNAL_DB=true python scripts/geocode_staging.py \
  --ids-file "reports/scraping_runs/extractor_missing_selector_fix_20260606_1129/geocoding_ids_24_props.csv" \
  --max-requests 10 \
  --commit \
  --report "reports/scraping_runs/extractor_missing_selector_fix_20260606_1129/geocoding_commit_24_props.md"
```

**Esperando autorización antes de ejecutar.**

---

## Confirmación de seguridad

| Verificación | Estado |
|---|---|
| Nominatim llamado | ✗ NO (dry-run, 0 requests) |
| Neon modificado | ✗ NO (rollback) |
| Supabase tocado | ✗ NO |
| publish_queue modificado | ✗ NO |
| frontend modificado | ✗ NO |
| `.env` modificado | ✗ NO |
| git commit | ✗ NO |
| git push | ✗ NO |
| datos históricos tocados | ✗ NO (ids-file aísla exactamente estos 10) |

---

*Generado al finalizar geocode_staging.py --dry-run · sesión 2026-06-06*
