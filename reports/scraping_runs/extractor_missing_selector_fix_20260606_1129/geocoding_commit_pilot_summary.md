# Geocoding commit piloto — 2 IDs alta confianza

- Fecha: 2026-06-06
- Modo: **commit** (accion_final=commit)
- IDs procesados: 81047, 81048 (staging_ids exactos via --ids-file)
- Proveedor: Nominatim (OSM)
- 81036 excluido: sin filtro de precisión en el script → riesgo de centroide genérico

---

## Resultado del commit piloto

| Métrica | Valor |
|---|---|
| filas_leidas | **2** |
| done | **0** |
| failed | **2** |
| skipped | **0** |
| requests_usados | **2** |
| accion_final | **commit** |

---

## Resultado por ID

| staging_id | Tipo | Dirección | Query enviada a Nominatim | Resultado | lat | lon | precision |
|---|---|---|---|---|---|---|---|
| 81047 | local / alquiler | calle Salta 329 | `calle Salta 329, Cafayate, Argentina` | **failed** | NULL | NULL | NULL |
| 81048 | casa / alquiler | Vertientes 57 | `Vertientes 57, Cafayate, Salta, Argentina` | **failed** | NULL | NULL | NULL |

**Error en ambos**: `"Sin resultados de geocoding"` — Nominatim no encontró ningún resultado.

---

## Estado post-commit en Neon

### propiedades_staging

| id | geocoding_status | latitud | longitud | score |
|---|---|---|---|---|
| 81047 | **failed** | NULL | NULL | 100 |
| 81048 | **failed** | NULL | NULL | 80 |

### geocoding_results — 2 nuevas filas insertadas

| propiedad_id | direccion_geocoding | status | error |
|---|---|---|---|
| 81047 | calle Salta 329, Cafayate, Argentina | error | Sin resultados de geocoding |
| 81048 | Vertientes 57, Cafayate, Salta, Argentina | error | Sin resultados de geocoding |

**Ninguna coordenada almacenada** — el script se comportó correctamente: falla limpia sin datos sucios.

---

## Análisis de por qué fallaron

### Causa raíz: cobertura OSM de Cafayate

Cafayate es una ciudad pequeña (~15.000 hab.) en Salta. OpenStreetMap — la fuente de Nominatim — tiene cobertura limitada a nivel de calle para ciudades de ese tamaño en Argentina. Las direcciones específicas ("calle Salta 329", "Vertientes 57") no están en el índice de Nominatim.

### Variantes de query intentadas: solo 1

`build_query_variants()` en geocoder.py solo genera variantes alternativas para patrones específicos (`Pte. Roca`, `1ro. de Mayo`, etc.). Para estas direcciones genéricas, solo se intentó 1 query por prop. No hubo fallbacks.

| ID | Queries intentadas | Resultado |
|---|---|---|
| 81047 | 1 ("calle Salta 329, Cafayate, Argentina") | 0 resultados |
| 81048 | 1 ("Vertientes 57, Cafayate, Salta, Argentina") | 0 resultados |

### Observación sobre 81047

La query para 81047 omitió la provincia "Salta" deliberadamente: `"calle Salta 329, Cafayate, Argentina"` — el geocoder detectó que "Salta" es parte del nombre de la calle ("calle Salta") y evitó duplicar "Salta, Salta" en la query. Comportamiento correcto.

---

## ¿Las coordenadas almacenadas son aceptables?

**No aplica** — no se almacenaron coordenadas. El script falló limpiamente:
- `lat=NULL, lon=NULL` en ambos props
- `geocoding_status=failed` (no "done" con coord falsa)
- `geocoding_results.status=error`

El pipeline no almacenó coordenadas genéricas ni centroides de ciudad. ✅

---

## ¿Conviene avanzar con las 4 de Pueblo Nuevo (81038, 81041, 81042, 81044)?

**NO, no conviene en este momento.**

Razonamiento:
- Las 2 direcciones de **mayor calidad** del batch (calle Salta 329 y Vertientes 57) no pudieron geocodificarse con Nominatim
- Las 4 de Pueblo Nuevo son referencias catastrales (`Mza. 21`, `Mza. 46`, etc.) — aún más genéricas que las anteriores
- El resultado esperado sería idéntico: `failed`, 0 coords, 4 requests Nominatim consumidos sin resultado útil

**Resultado esperado si se intenta**: 4 × failed, 0 × done. No vale la pena consumir los requests de Nominatim.

---

## ¿Y 81036 (Haras La Querencia 800)?

**Tampoco conviene.**

Razones:
1. Si "calle Salta 329" no fue encontrada, un nombre de propiedad privada tampoco lo será
2. El script no tiene filtro de precisión: si Nominatim devolviera coordenadas aproximadas, las guardaría como `done`
3. Riesgo adicional: sin dato seguro

---

## ¿Conviene hacer publish_queue dry-run ahora?

**Sí, es viable y no tiene riesgo.**

Las 24 props están en `propiedades_staging` con:
- 2 props recién marcadas como `geocoding_status=failed` (no bloquea publish_queue)
- 8 props con `geocoding_status=skipped` — solo ciudad/provincia aproximada
- 10 props con `geocoding_status=skipped` — solo provincia
- 3 props con `geocoding_status=pending` (watson) — sin datos
- 1 prop con `geocoding_status=pending` (81036 — no procesada)

`build_publish_queue.py` típicamente filtra por `validation_score` mínimo y `status='staging'`. Las props con `geocoding_status=failed` generalmente entran con un score penalizado o sin coords.

Un **publish_queue dry-run** mostraría cuántas de las 24 entrarían a la cola de publicación y con qué prioridad — sin modificar Supabase ni publicar nada.

---

## Opciones para el geocoding de innoacafayate

| Opción | Pros | Contras |
|---|---|---|
| **Dejar como failed** — avanzar con publish_queue | Datos limpios, sin coords falsas | Props sin ubicación en mapa |
| **Esperar actualización OSM de Cafayate** | Gratuito | Incierto, puede tardar meses |
| **Google Maps Geocoding API** | Alta cobertura para Argentina | Requiere API key + costo por request |
| **Geocodificar manualmente las 7** | Precisión perfecta | Trabajo manual |
| **Usar city centroid** | Cubre coords mínimas | Precisión baja — NO recomendado si se quiere calidad |

---

## Confirmación de seguridad

| Verificación | Estado |
|---|---|
| Supabase tocado | ✗ NO |
| publish_queue modificado | ✗ NO |
| frontend modificado | ✗ NO |
| `.env` modificado | ✗ NO |
| datos históricos tocados | ✗ NO (ids-file aísla exactamente 2 IDs) |
| git commit | ✗ NO |
| git push | ✗ NO |
| coordenadas incorrectas almacenadas | ✗ NO (failed limpio, lat/lon=NULL) |
| propiedades_staging corrompidas | ✗ NO (geocoding_status=failed es reversible) |

---

*Generado al finalizar geocode_staging.py --commit piloto · sesión 2026-06-06*
